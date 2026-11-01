public class oldV {
    // readable: 10% off from 10 items, members get another 5% (each discount rounded down on its own)
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int off = 0;
        total = price * qty;
        if (qty >= 10) {
            off = total / 10;
        }
        if (member == 1) {
            off = off + total / 20;
        }
        total = total - off;
        return total;
    }
}
