public class newV {
    // bound changed to <= n: adds n itself when n is even
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i <= n; i++) {
            if (i % 2 == 0) {
                sum = sum + i;
            }
        }
        return sum;
    }
}
