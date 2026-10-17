public class oldV {
    // readable: price * rate recomputed inside the loop
    public static double snippet(int price, int rate, int n) {
        int i = 0;
        int unit = 0;
        int total = 0;
        for (i = 0; i < n; i++) {
            total = total + price * rate + i;
        }
        return total;
    }
}
