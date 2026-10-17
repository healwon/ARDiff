public class newV {
    // fast: Horner's rule, 3 multiplications instead of 6
    public static double snippet(int x) {
        int result = ((3 * x + 2) * x - 5) * x + 7;
        return result;
    }
}
