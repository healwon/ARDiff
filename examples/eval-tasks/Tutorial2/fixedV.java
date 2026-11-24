public class fixedV {
    // reference fix: b replaces a only when b is smaller
    public static double snippet(int a, int b) {
        int smaller = a;
        if (b < smaller) {
            smaller = b;
        }
        return smaller;
    }
}
