public class newV {
    // "hot path first": check the upper bound first. Differs when lo > hi (x below lo and above hi)
    public static double snippet(int x, int lo, int hi) {
        int r = x;
        if (x > hi) {
            r = hi;
        } else if (x < lo) {
            r = lo;
        }
        return r;
    }
}
