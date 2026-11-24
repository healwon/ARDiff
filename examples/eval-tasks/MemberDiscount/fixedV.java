public class fixedV {
    // reference fix: every member gets the 5%, and each discount is taken from the unit price as before
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
        total = total - (price * (pct / 10) / 10 + price * (pct % 10 / 5) / 20) * qty;
        return total;
    }
}
