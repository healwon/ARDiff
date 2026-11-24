public class newV {
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
        total = total - total * pct / 100;
        return total;
    }
}
