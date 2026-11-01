public class fixedV {
    // reference fix: round each discount per unit price, as before; pct only says which discounts apply
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int pct = 0;
        total = price * qty;
        if (qty >= 10) {
            pct = pct + 10;
        }
        if (member == 1 && total >= 100) {
            pct = pct + 5;
        }
        total = (price - price * (pct / 10) / 10 - price * (pct % 10 / 5) / 20) * qty;
        return total;
    }
}
