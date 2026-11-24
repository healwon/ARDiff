public class oldV {
    // Returns 1 for a leap year, 0 otherwise: divisible by 4, except centuries, except every 400 years
    public static double snippet(int year) {
        int leap = 0;
        if (year % 4 == 0) {
            if (year % 100 == 0) {
                if (year % 400 == 0) {
                    leap = 1;
                }
            } else {
                leap = 1;
            }
        }
        return leap;
    }
}
