public class oldV {
    // before: 10% off for 10 or more items; members get another 5% off
    //         (each discount is computed from the price separately)
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int off = 0;
        total = price * qty;
        if (qty >= 10) {
            off = price / 10 * qty;
        }
        if (member == 1) {
            off = off + price / 20 * qty;
        }
        total = total - off;
        return total;
    }
}
