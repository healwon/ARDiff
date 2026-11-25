public class fixedV {
    // reference fix: count from 50 (int division rounds toward zero, so 51..59 gave 1), and 100 is valid
    public static double snippet(int score) {
        int g = 0;
        g = (score - 50) / 10;
        g = Math.max(0, Math.min(4, g));
        if (score < 0 || score > 100) {
            g = -1;
        }
        return g;
    }
}
