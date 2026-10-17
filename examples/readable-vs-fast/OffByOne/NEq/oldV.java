public class oldV {
    // readable: sum of 0 + 1 + ... + (n - 1)
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < n; i++) {
            sum = sum + i;
        }
        return sum;
    }
}
