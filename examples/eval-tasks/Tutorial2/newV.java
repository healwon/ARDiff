public class newV {
    // refactored for readability: start from a, keep the smaller value in a named variable
    public static double snippet(int a, int b) {
        int smaller = a;
        if (b > smaller) {
            smaller = b;
        }
        return smaller;
    }
}
