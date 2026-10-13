public class oldV {
    public static double snippet(double price, int qty) {
        double base = price * qty;
        double tax = base * 0.1;
        double total = base + tax;
        if (qty > 10)
            total = total * 0.9;
        return total;
    }
}
