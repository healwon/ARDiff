public class newV {
    // the member discount now needs an order of at least 100; discounts collected as one percentage
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int off = 0;
        int pct = 0;
        total = price * qty;
        if (qty >= 10) {
            pct = pct + 10;
        }
        if (member == 1 && total >= 100) {
            pct = pct + 5;
        }
        off = total * pct / 100;
        total = total - off;
        return total;
    }
}
