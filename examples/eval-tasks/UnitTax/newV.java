public class newV {
    // tax per unit: price / 10 drops the remainder before multiplying
    public static double snippet(int price, int qty) {
        int total = 0;
        int tax = 0;
        total = price * qty;
        tax = price / 10 * qty;
        total = total + tax;
        return total;
    }
}
