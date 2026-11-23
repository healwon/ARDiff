public class specV {
    // spec: the smaller of a and b, but never above 50
    public static double snippet(int a, int b) {
        int r = 0;
        if (a < b) {
            r = a;
        } else {
            r = b;
        }
        if (r > 50) {
            r = 50;
        }
        return r;
    }
}
