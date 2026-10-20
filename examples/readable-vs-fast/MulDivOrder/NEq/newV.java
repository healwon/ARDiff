public class newV {
    // "overflow-safe": divide first, but the remainder of x / 4 is lost
    public static double snippet(int x) {
        int r = 0;
        r = x / 4 * 3;
        return r;
    }
}
