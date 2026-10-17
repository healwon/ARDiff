public class newV {
    // fast: square twice (2 multiplications instead of 3)
    public static double snippet(int x) {
        int sq = 0;
        int p = 0;
        sq = x * x;
        p = sq * sq;
        return p;
    }
}
