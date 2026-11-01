public class oldV {
    // readable: the sum of the decimal digits of n (0 for negative n)
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = n;
        while (m > 0) {
            sum = sum + m % 10;
            m = m / 10;
        }
        return sum;
    }
}
