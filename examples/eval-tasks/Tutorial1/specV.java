public class specV {
    // spec: the larger of a and b, but never below 0
    public static double snippet(int a, int b) {
        int r = 0;
        if (a > b) {
            r = a;
        } else {
            r = b;
        }
        if (r < 0) {
            r = 0;
        }
        return r;
    }
}
