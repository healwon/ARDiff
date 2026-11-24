public class newV {
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = n;
        while (abs(m) > 10) {
            sum = sum + abs(m) % 10;
            m = m / 10;
        }
        sum = sum + m;
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
