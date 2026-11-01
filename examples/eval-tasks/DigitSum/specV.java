public class specV {
    // spec: the digit sum of n, taking negative n by its absolute value
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = abs(n);
        while (m > 0) {
            sum = sum + m % 10;
            m = m / 10;
        }
        return sum;
    }

    public static int abs(int n) {
        if (n < 0) {
            return -n;
        } else {
            return n;
        }
    }
}
