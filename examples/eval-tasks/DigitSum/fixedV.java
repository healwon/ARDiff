public class fixedV {
    // reference fix: loop while two or more digits are left (m > 9), and add the last digit only for positive m
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        for (m = n; m > 9; m = m / 10) {
            sum = sum + m % 10;
        }
        if (m > 0) {
            sum = sum + m;
        }
        return sum;
    }
}
