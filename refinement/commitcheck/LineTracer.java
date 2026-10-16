import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;

import java.io.*;
import java.util.*;

/**
 * Records which source lines of one class run, in order, for each top-level call into it.
 *
 * usage: java -cp tools.jar:. LineTracer CLASSPATH MAIN_CLASS TARGET_CLASS OUT_JSON [MAX_STEPS]
 * MAIN_CLASS calls TARGET_CLASS's method once per input; every call that enters TARGET_CLASS from
 * outside starts a new segment. Output: [{"lines":[..], "ret":"..", "truncated":false}, ...]
 * (needs classes compiled with -g; JDK 8 tools.jar on the classpath)
 */
public class LineTracer {
    public static void main(String[] a) throws Exception {
        String cp = a[0], main = a[1], target = a[2], out = a[3];
        int maxSteps = a.length > 4 ? Integer.parseInt(a[4]) : 5000;

        LaunchingConnector lc = Bootstrap.virtualMachineManager().defaultConnector();
        Map<String, Connector.Argument> args = lc.defaultArguments();
        args.get("options").setValue("-cp \"" + cp + "\"");
        args.get("main").setValue(main);
        VirtualMachine vm = lc.launch(args);
        drain(vm.process().getInputStream());
        drain(vm.process().getErrorStream());

        EventRequestManager erm = vm.eventRequestManager();
        MethodEntryRequest me = erm.createMethodEntryRequest();
        me.addClassFilter(target);
        me.enable();
        MethodExitRequest mx = erm.createMethodExitRequest();
        mx.addClassFilter(target);
        mx.enable();

        List<List<Integer>> segs = new ArrayList<>();
        List<String> rets = new ArrayList<>();
        List<Boolean> cut = new ArrayList<>();
        StepRequest step = null;
        int depth = 0;
        boolean done = false;
        EventQueue q = vm.eventQueue();
        while (!done) {
            EventSet set = q.remove();
            for (Event ev : set) {
                if (ev instanceof MethodEntryEvent) {
                    if (depth++ == 0) {
                        segs.add(new ArrayList<Integer>());
                        rets.add(null);
                        cut.add(false);
                        if (step == null) {
                            step = erm.createStepRequest(((MethodEntryEvent) ev).thread(), StepRequest.STEP_LINE, StepRequest.STEP_INTO);
                            step.addClassFilter(target);
                            step.enable();
                        }
                        record(segs, cut, ((MethodEntryEvent) ev).location(), maxSteps);
                    }
                } else if (ev instanceof MethodExitEvent) {
                    if (--depth == 0) {
                        Value v = ((MethodExitEvent) ev).returnValue();
                        rets.set(rets.size() - 1, v == null ? "null" : v.toString());
                    }
                } else if (ev instanceof StepEvent) {
                    if (depth > 0) record(segs, cut, ((StepEvent) ev).location(), maxSteps);
                } else if (ev instanceof VMDisconnectEvent || ev instanceof VMDeathEvent) {
                    done = true;
                }
            }
            if (!done) set.resume();
        }

        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < segs.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append("{\"lines\":").append(segs.get(i).toString().replace(" ", ""))
              .append(",\"ret\":").append(json(rets.get(i)))
              .append(",\"truncated\":").append(cut.get(i)).append("}");
        }
        sb.append("]");
        try (Writer w = new OutputStreamWriter(new FileOutputStream(out), "UTF-8")) { w.write(sb.toString()); }
    }

    static void record(List<List<Integer>> segs, List<Boolean> cut, Location loc, int max) {
        List<Integer> s = segs.get(segs.size() - 1);
        int line = loc.lineNumber();
        if (line <= 0) return;
        if (s.size() >= max) { cut.set(cut.size() - 1, true); return; }
        if (s.isEmpty() || s.get(s.size() - 1) != line) s.add(line);
    }

    static String json(String s) {
        if (s == null) return "null";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
    }

    static void drain(final InputStream in) {
        Thread t = new Thread(() -> { try { byte[] b = new byte[4096]; while (in.read(b) >= 0) { } } catch (IOException ignored) { } });
        t.setDaemon(true);
        t.start();
    }
}
