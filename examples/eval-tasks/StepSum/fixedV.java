public class fixedV {
    // reference fix: keep the step of 2, keep the bound strict
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < n; i = i + 2) {
            sum = sum + i;
        }
        return sum;
    }
}
