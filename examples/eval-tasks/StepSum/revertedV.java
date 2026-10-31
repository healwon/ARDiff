public class revertedV {
    // naive rollback of the loop header: without the parity test this now sums every number
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < n; i++) {
            sum = sum + i;
        }
        return sum;
    }
}
