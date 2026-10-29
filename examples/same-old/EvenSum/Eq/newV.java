public class newV {
    // evenness tested by halving, and the even number rebuilt from its half: equal only inside the test
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < n; i++) {
            if ((i / 2) * 2 == i) {
                sum = sum + 2 * (i / 2);
            }
        }
        return sum;
    }
}
