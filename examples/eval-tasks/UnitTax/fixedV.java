public class fixedV {
    // reference fix: per-unit tax cannot round like the total; the change itself has to go
    public static double snippet(int price, int qty) {
        int total = 0;
        int tax = 0;
        total = price * qty;
        tax = total / 10;
        total = total + tax;
        return total;
    }
}
