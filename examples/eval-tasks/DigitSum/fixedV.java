public class fixedV {
    // reference fix: the loop must run while two or more digits are left (m >= 10)
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = Math.abs(n);
        while (m >= 10) {
            sum = sum + m % 10;
            m = m / 10;
        }
        sum = sum + m;
        return sum;
    }
}
