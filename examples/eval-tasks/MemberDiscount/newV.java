public class newV {
    // refactored for readability: the discounts are collected as one percentage
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int pct = 0;
        total = price * qty;
        if (qty >= 10) {
            pct = pct + 10;
        }
        if (member == 1) {
            pct = pct + 5;
        }
        total = total - total * pct / 100;
        return total;
    }
}
