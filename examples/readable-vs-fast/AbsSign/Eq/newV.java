public class newV {
    // fast: no multiplication, negate when the sign computed above is negative
    public static double snippet(int x) {
        int s = 1;
        int r = 0;
        if (x < 0) {
            s = -1;
        }
        r = s < 0 ? -x : x;
        return r;
    }
}
