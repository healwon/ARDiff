public class fixedV {
    // reference fix: the replacement takes b
    public static double snippet(int a, int b) {
        int r = a;
        if (b > a) {
            r = b;
        }
        return r;
    }
}
