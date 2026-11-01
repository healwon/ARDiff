public class newV {
    // spec: each discount is computed from the price separately still
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int off = 0;
        total = price * qty;
        if (qty >= 10) {
            off = price / 10;
        }
        if (member == 1 && total >= 100) {
            off = off + price / 20;
        }
        total = (price - off) * qty;
        return total;
    }
}
