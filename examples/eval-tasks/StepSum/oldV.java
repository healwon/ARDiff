public class oldV {
    // readable: sum of the even numbers below n
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < n; i++) {
            if (i % 2 == 0) {
                sum = sum + i;
            }
        }
        return sum;
    }
}
