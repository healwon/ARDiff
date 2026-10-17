public class newV {
    // overflow-safe rewrite: rounds differently when the sum is negative and odd (a = -1, b = 0)
    public static double snippet(int a, int b) {
        int avg = a + (b - a) / 2;
        return avg;
    }
}
