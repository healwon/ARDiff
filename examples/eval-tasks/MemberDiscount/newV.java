public class newV {
    // after: the member discount now requires an order total of at least 100.
    // constraints:
    //   1. do not change either of the two if statements
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
