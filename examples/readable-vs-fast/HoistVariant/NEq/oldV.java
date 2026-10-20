public class oldV {
    // readable: each step adds price * i
    public static double snippet(int price, int n) {
        int i = 0;
        int step = 0;
        int total = 0;
        for (i = 0; i < n; i++) {
            total = total + price * i;
        }
        return total;
    }
}
