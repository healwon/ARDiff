public class fixedV {
    // reference fix: loop while m > 0, and no last digit added after the loop
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = n;
        while (m > 0) {
            sum = sum + abs(m) % 10;
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
