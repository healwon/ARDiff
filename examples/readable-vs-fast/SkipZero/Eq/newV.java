public class newV {
    // fast: start at 1, the i = 0 iteration adds nothing
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 1; i < n; i++) {
            sum = sum + i;
        }
        return sum;
    }
}
