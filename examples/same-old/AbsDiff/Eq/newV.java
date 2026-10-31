public class newV {
    // order the two values first, then subtract the smaller from the larger
    public static double snippet(int a, int b) {
        int hi = 0;
        int lo = 0;
        int d = 0;
        hi = a;
        lo = b;
        if (b > a) {
            hi = b;
            lo = a;
        }
        d = hi - lo;
        return d;
    }
}
