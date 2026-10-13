public class newV {
    public static double snippet(double price, int qty) {
        double base = price * qty;
        double tax = base * 0.1;
        double total = base + tax;
        if (qty >= 11)
            total = (base + tax) * 0.9;
        return total;
    }
}
