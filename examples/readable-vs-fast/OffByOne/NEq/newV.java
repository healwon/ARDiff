public class newV {
    // "tidied" bounds: i <= n also adds n itself
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 1; i <= n; i++) {
            sum = sum + i;
        }
        return sum;
    }
}
