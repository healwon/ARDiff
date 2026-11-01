public class specV {
    // spec: the old rule, but members get their 5% only on orders of at least 100
    public static double snippet(int price, int qty, int member) {
        int total = 0;
        int off = 0;
        total = price * qty;
        if (qty >= 10) {
            off = total / 10;
        }
        if (member == 1 && total >= 100) {
            off = off + total / 20;
        }
        total = total - off;
        return total;
    }
}
