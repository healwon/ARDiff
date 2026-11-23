public class fixedV {
    // reference fix: the else branch takes b
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
