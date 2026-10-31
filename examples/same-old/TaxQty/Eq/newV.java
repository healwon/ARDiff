public class newV {
    // total * 1.1 in one division: tax now holds the remainder, which makes 11 * total - tax an exact multiple of 10
    public static double snippet(int price, int qty) {
        int total = 0;
        int tax = 0;
        total = price * qty;
        tax = total - total / 10 * 10;
        total = (total * 11 - tax) / 10;
        return total;
    }
}
