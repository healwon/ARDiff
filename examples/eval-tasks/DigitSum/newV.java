public class newV {
    // refactored for readability: a for loop over the digits; the last digit is added after the loop
    public static double snippet(int n) {
        int sum = 0;
        int m = 0;
        for (m = n; m > 10; m = m / 10) {
            sum = sum + m % 10;
        }
        sum = sum + m;
        return sum;
    }
}
