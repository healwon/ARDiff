public class fixedV {
    // reference fix: the else branch takes b, and the result is not clamped at 0
    public static double snippet(int a, int b) {
        int r = 0;
        if (a > b) {
            r = a;
        } else {
            r = b;
        }
        return r;
    }
}
