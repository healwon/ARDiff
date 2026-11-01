public class fixedV {
    // reference fix: one percentage rounds differently from two discounts, so each part is rounded on its own again
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
        off = total * (pct / 10) / 10 + total * (pct % 10 / 5) / 20;
        total = total - off;
        return total;
    }
}
