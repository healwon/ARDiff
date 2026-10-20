public class newV {
    // fast: step by 3, but starting at 3 skips 0
    public static double snippet(int n) {
        int i = 0;
        int count = 0;
        for (i = 3; i < n; i = i + 3) {
            if (i % 3 == 0) {
                count = count + 1;
            }
        }
        return count;
    }
}
