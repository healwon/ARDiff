public class newV {
    // three edits that keep each path: the difference written as -b + a, the test as 0 > d, the flip as 0 - d
    public static double snippet(int a, int b) {
        int d = 0;
        d = -b + a;
        if (0 > d) {
            d = 0 - d;
        }
        return d;
    }
}
