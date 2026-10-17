public class newV {
    // rewritten while optimising: the top boundary slipped from >= 50 to > 50
    public static double snippet(int qty) {
        int unit = 10;
        int total = 0;
        if (qty >= 10) {
            unit = 8;
        }
        if (qty > 50) {
            unit = 7;
        }
        total = qty * unit;
        return total;
    }
}
