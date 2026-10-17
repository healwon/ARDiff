public class oldV {
    // readable: below the range -> lo, above -> hi, otherwise x
    public static double snippet(int x, int lo, int hi) {
        int r = x;
        if (x < lo) {
            r = lo;
        } else if (x > hi) {
            r = hi;
        }
        return r;
    }
}
