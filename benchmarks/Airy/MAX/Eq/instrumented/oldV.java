package demo.benchmarks.Airy.MAX.Eq.instrumented;
import equiv.checking.symbex.UnInterpreted;
public class oldV{
    public static double snippet(double a, double b) {
        if (b > a)
            return b;
        else
            return a;
    }
}
