public class newV {
    // negative numbers now count by their digits too; the last digit is added after the loop
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        m = Math.abs(n);
        while (m > 10) {
            sum = sum + m % 10;
            m = m / 10;
        }
        sum = sum + m;
        return sum;
    }
}
