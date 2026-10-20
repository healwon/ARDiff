public class oldV {
    // readable: count the multiples of 3 below n
    public static double snippet(int n) {
        int i = 0;
        int count = 0;
        for (i = 0; i < n; i++) {
            if (i % 3 == 0) {
                count = count + 1;
            }
        }
        return count;
    }
}
