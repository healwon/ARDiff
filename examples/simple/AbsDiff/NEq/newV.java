public class newV {
    // off-by-one guard: a difference of -1 is no longer flipped
    public static double snippet(int a, int b) {
        int d = 0;
        d = a - b;
        if (d < -1) {
            d = -d;
        }
        return d;
    }
}
