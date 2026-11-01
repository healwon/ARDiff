public class oldV {
    // before: returns the sum of the decimal digits of n
    //         n should be positive; returns 0 when n is negative
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
